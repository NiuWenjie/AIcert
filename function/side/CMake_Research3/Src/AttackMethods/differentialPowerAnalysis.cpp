#include<stdio.h>
#include<stdlib.h>
#include<time.h>
#include <cstring>
#include "../../Inc/side_channel_attack_methods.h"
#include "../../Inc/TRACE/Trace.h"
#include "../../Inc/BASETOOL/BaseTools.h"
#include "../../Inc/CNNModel/cnn.h"
// #include "../../Inc/CNNModel/arm_nnexamples_cifar10_parameter.h"
// #include "../../Inc/CNNModel/arm_nnexamples_cifar10_weights.h"



void differentialPowerAnalysis(Parameters* param, int8_t* (*f)(Parameters*)){

    //fmap初始化
    q7_t fmap[param->getFmapNum()]={0};
    fmapInitial(param, fmap);


    //wt初始化
    q7_t wt[param->getGuessSize()];
    for(int i=0; i < param->getGuessSize(); i++){
        wt[i]=i-128;
    }

    //一次读量初始化
	float* sample[param->getPointNum()] = {nullptr};
    for(int i=0;i< param->getPointNum() ;i++){
        sample[i]=(float*)malloc(param->getTraceNum()*sizeof(float));
        std::memset(sample[i], 0.0, param->getTraceNum() * sizeof(float));
    }

    Trace traceR(param->getRandFile());
	Trace traceS(param->getSampleFile());
    TrsData trsDataR;
	TrsData trsDataS;

    TrsData* trsData_result=(TrsData*)malloc(param->getGuessSize() * sizeof(TrsData));
    uint8_t* hw[param->getGuessSize()] = {nullptr};
    for(int i=0;i<param->getGuessSize();i++){
        hw[i]=(uint8_t*)malloc(param->getTraceNum() * sizeof(uint8_t));
        std::memset(hw[i], 0, param->getTraceNum() * sizeof(uint8_t));
        trsData_result[i].samples=(float*)malloc(param->getPointNum() * sizeof(float));
        std::memset(trsData_result[i].samples, 0.0, param->getPointNum() * sizeof(float));
    }

    float result_max[param->getGuessSize()]={0.0};
    float result_max_abs[param->getGuessSize()]={0.0};

    //attackindex -->> i j k m n l
    int attackIndex1 = *param->getAttackIndex();
    int attackIndex2 = *(param->getAttackIndex()+1);
    int attackIndex3 = *(param->getAttackIndex()+2);
    param->setForI(attackIndex1/75);//
    param->setForJ(attackIndex2);
    param->setForK(attackIndex3);
    param->setForM(attackIndex1%75/15);//
    param->setForN(attackIndex1%75%15/3);//
    param->setForL(attackIndex1%3);//


    for(int i=0; i < param->getTraceNum(); i++){

        

        //读一条
        traceS.readIndexTrace(&trsDataS,i);
        traceR.readIndexTrace(&trsDataR,i); 

        param->setImageDataPoint(trsDataR.data);//param读imagedata参数
        //像素初始化
        for(int j=0;j < param->getGuessSize();j++){ 
            
            
            fmap[*param->getAttackIndex()] = wt[j];
            // param->setFmapPoint(fmap);//param读fmap参数
            
            #if 1

            (*f)(param);
            hw[j][i] = param->getMidHW();
            // printf("%d ", hw[j][i]);

            #endif

        }

        // printf("%d ", i);
        // printf("\n");
        
        for(int j=0; j < param->getPointNum() ; j++){
            sample[j][i]=trsDataS.samples[j+param->getPointNumStart()];
        }  
        
    }

    



    //差分计算
    for (int i = 0; i < param->getGuessSize(); i++){
        for (int j = 0; j < param->getPointNum(); j++){
            
            //问题出现在这行，检查内存是否溢出？
            trsData_result[i].samples[j] = (float)abs(BaseTools::diff(hw[i], sample[j], param->getTraceNum(),25));
            // printf("2\n");
            
            // printf("%f,",trsData_result[i].samples[startPoint_r+j]);
            if(i==128){
                
                trsData_result[i].samples[j] =0;
            }
        }
        result_max[i]=trsData_result[i].samples[BaseTools::findMaxCorr(trsData_result[i].samples,param->getPointNum())];
        #if 1
        printf("%d_max:%f;\n",i-128,result_max[i]);
        #endif


        
    }


        
    
    //存储trs----START------------------------------------------------
    ofstream* outfile=new ofstream();   
    outfile->open(param->getOutFile(), ios::out | ios::binary | ios::trunc);

    TrsHead trsHead_result;
    trsHead_result.NT = param->getGuessSize();
    trsHead_result.NS = param->getPointNum();
    trsHead_result.DS = 0;
    trsHead_result.YS = 1;
    trsHead_result.SC = 0x14;//float存储类型
    trsHead_result.GT_length = 0;
    trsHead_result.DC_length = 0;
    trsHead_result.XL_length = 0;
    trsHead_result.YL_length = 0;
    trsHead_result.TS = 0;
    Trace::writeHead(outfile, trsHead_result);
    
    for(int i= 0;i<param->getGuessSize();i++){
        Trace::writeNext(outfile, &trsData_result[i], trsHead_result);
    }
    
    //存储trs-----END-------------------------------------------------
    
    #if 0
    for(int i=0;i<GUESS_SIZE;i++){
    trsData2->samples[i]=result_max[i];
    // printf("%f ",result_max[i]); 
    printf("%f,",result_max[i]); 
    }

    #endif

    #if 1
    BaseTools::bubbleSort(result_max,wt,param->getGuessSize());
    for(int re=0;re<param->getGuessSize();re++){
        // printf("%f ",result_max[re]);
        // printf("[%d]:%d;",re+1,result_max_index[re]-128);
        printf("%d ",wt[re]);
    }

    printf("\n");

    for(int i=0;i<param->getGuessSize();i++){
        wt[i]=i-128;
    }

    #endif
    
    
    for(int i=0;i < param->getGuessSize(); i++){
        free(hw[i]);
        free(trsData_result[i].samples);
    }
    free(trsData_result);
    
    for(int i=0;i < param->getPointNum();i++){
        free(sample[i]);
    }

    free(trsDataS.samples);
    free(trsDataS.data);
    free(trsDataS.TSData);

    free(trsDataR.samples);
    free(trsDataR.data);
    free(trsDataR.TSData);

    outfile->close();
    free(outfile);
    

    return;

    
    
}






void differentialPowerAnalysis_correlation_distinguish_index(Parameters* param, int8_t* (*f)(Parameters*), float** result, int index, int tem_trace_num){

    //fmap初始化
    q7_t fmap[param->getFmapNum()]={0};
    fmapInitial(param, fmap);


    //wt初始化
    q7_t wt[param->getGuessSize()];
    for(int i=0; i < param->getGuessSize(); i++){
        wt[i]=i-128;
    }

    //一次读量初始化
	float* sample[param->getPointNum()] = {nullptr};
    for(int i=0;i< param->getPointNum() ;i++){
        sample[i]=(float*)malloc(tem_trace_num*sizeof(float));
        std::memset(sample[i], 0.0, tem_trace_num * sizeof(float));
    }

    Trace traceR(param->getRandFile());
	Trace traceS(param->getSampleFile());
    TrsData trsDataR;
	TrsData trsDataS;

    TrsData* trsData_result=(TrsData*)malloc(param->getGuessSize() * sizeof(TrsData));
    uint8_t* hw[param->getGuessSize()] = {nullptr};
    for(int i=0;i<param->getGuessSize();i++){
        hw[i]=(uint8_t*)malloc(tem_trace_num * sizeof(uint8_t));
        std::memset(hw[i], 0, tem_trace_num * sizeof(uint8_t));
        trsData_result[i].samples=(float*)malloc(param->getPointNum() * sizeof(float));
        std::memset(trsData_result[i].samples, 0.0, param->getPointNum() * sizeof(float));
    }

    float result_max[param->getGuessSize()]={0.0};
    float result_max_abs[param->getGuessSize()]={0.0};

    //attackindex -->> i j k m n l
    int attackIndex1 = *param->getAttackIndex();
    int attackIndex2 = *(param->getAttackIndex()+1);
    int attackIndex3 = *(param->getAttackIndex()+2);
    param->setForI(attackIndex1/75);//
    param->setForJ(attackIndex2);
    param->setForK(attackIndex3);
    param->setForM(attackIndex1%75/15);//
    param->setForN(attackIndex1%75%15/3);//
    param->setForL(attackIndex1%3);//


    for(int i=0; i < tem_trace_num; i++){

        

        //读一条
        traceS.readIndexTrace(&trsDataS,i);
        traceR.readIndexTrace(&trsDataR,i); 

        param->setImageDataPoint(trsDataR.data);//param读imagedata参数
        //像素初始化
        for(int j=0;j < param->getGuessSize();j++){ 
            
            
            fmap[*param->getAttackIndex()] = wt[j];
            // param->setFmapPoint(fmap);//param读fmap参数
            
            #if 1

            (*f)(param);
            hw[j][i] = param->getMidHW();
            // printf("%d ", hw[j][i]);

            #endif

        }

        // printf("%d ", i);
        // printf("\n");
        
        for(int j=0; j < param->getPointNum() ; j++){
            sample[j][i]=trsDataS.samples[j+param->getPointNumStart()];
        }  
        
    }

    



    //计算相关性
    for (int i = 0; i < param->getGuessSize(); i++){
        for (int j = 0; j < param->getPointNum(); j++){
            
            //问题出现在这行，检查内存是否溢出？
            trsData_result[i].samples[j] = (float)abs(BaseTools::diff(hw[i], sample[j], tem_trace_num, 25));
            // printf("2\n");
            
            // printf("%f,",trsData_result[i].samples[startPoint_r+j]);
            if(i==128){
                
                trsData_result[i].samples[j] =0;
            }
        }
        result_max[i]=trsData_result[i].samples[BaseTools::findMaxCorr(trsData_result[i].samples,param->getPointNum())];
        #if 0
        printf("%d_max:%f;\n",i-128,result_max[i]);
        #endif


        
    }
    
    #if 1 //output in result**


    for(int i=0;i<param->getGuessSize();i++){
        result[i][index]=result_max[i];
        // printf("%f ",result_max[i]); 
        // printf("%f,",result_max[i]); 
    }



    #endif




        
    

    #if 0//存储trs----START------------------------------------------------
    ofstream* outfile=new ofstream();   
    outfile->open(param->getOutFile(), ios::out | ios::binary | ios::trunc);

    TrsHead trsHead_result;
    trsHead_result.NT = param->getGuessSize();
    trsHead_result.NS = param->getPointNum();
    trsHead_result.DS = 0;
    trsHead_result.YS = 1;
    trsHead_result.SC = 0x14;//float存储类型
    trsHead_result.GT_length = 0;
    trsHead_result.DC_length = 0;
    trsHead_result.XL_length = 0;
    trsHead_result.YL_length = 0;
    trsHead_result.TS = 0;
    Trace::writeHead(outfile, trsHead_result);
    
    for(int i= 0;i<param->getGuessSize();i++){
        Trace::writeNext(outfile, &trsData_result[i], trsHead_result);
    }
    
    #endif//存储trs-----END-------------------------------------------------
    


    

    #if 0
    BaseTools::bubbleSort(result_max,wt,param->getGuessSize());
    for(int re=0;re<param->getGuessSize();re++){
        // printf("%f ",result_max[re]);
        // printf("[%d]:%d;",re+1,result_max_index[re]-128);
        printf("%d ",wt[re]);
    }

    printf("\n");

    for(int i=0;i<param->getGuessSize();i++){
        wt[i]=i-128;
    }

    #endif
    
    
    for(int i=0;i < param->getGuessSize(); i++){
        free(hw[i]);
        free(trsData_result[i].samples);
    }
    free(trsData_result);
    
    for(int i=0;i < param->getPointNum();i++){
        free(sample[i]);
    }

    free(trsDataS.samples);
    free(trsDataS.data);
    free(trsDataS.TSData);

    free(trsDataR.samples);
    free(trsDataR.data);
    free(trsDataR.TSData);


    // outfile->close();
    // free(outfile);
    

    return;

    
    
}

void differentialPowerAnalysis_correlation_distinguish(Parameters* param, int8_t* (*f)(Parameters*)){
    ofstream* outfile=new ofstream();   
    outfile->open(param->getOutFile(), ios::out | ios::binary | ios::trunc);

    int bias=50;
    int gap=50;

    float** result=(float**)malloc(param->getGuessSize()*sizeof(float*));
    for(int i =0 ;i<param->getGuessSize();i++){
        result[i]=(float*)malloc(((param->getTraceNum()-bias)/gap+1)*sizeof(float));
        memset(result[i], 0.0, ((param->getTraceNum()-bias)/gap+1));
    }

    for(int index=0; index < (param->getTraceNum()-bias)/gap+1; index++){
        
        // param->setTraceNum(index*gap+bias);
        // printf("%d %d\n", index,index*gap+bias);
        differentialPowerAnalysis_correlation_distinguish_index(param, f, result, index, index*gap+bias);
    }

    for(int i =0;i<param->getGuessSize();i++){
        for(int j =0; j<(param->getTraceNum()-bias)/gap+1; j++){
            *outfile<<result[i][j]<<" ";
        }
        *outfile<<"\n";
    }
    
    for(int i =0 ;i<param->getGuessSize();i++){
        free(result[i]);
    }
    free(result);
    outfile->close();
    free(outfile);

}





//---------------优化--------------------------------------------------------
void generate_midvaluehw_samples_dpa(Parameters* param, int8_t* (*f)(Parameters*), float** sample, uint8_t** hw){

    //fmap初始化
    q7_t fmap[param->getFmapNum()]={0};
    fmapInitial(param, fmap);


    //wt初始化
    q7_t wt[param->getGuessSize()];
    for(int i=0; i < param->getGuessSize(); i++){
        wt[i]=i-128;
    }

    Trace traceR(param->getRandFile());
	Trace traceS(param->getSampleFile());
    TrsData trsDataR;
	TrsData trsDataS;

    float result_max[param->getGuessSize()]={0.0};
    float result_max_abs[param->getGuessSize()]={0.0};

    //attackindex -->> i j k m n l
    int attackIndex1 = *param->getAttackIndex();
    int attackIndex2 = *(param->getAttackIndex()+1);
    int attackIndex3 = *(param->getAttackIndex()+2);
    param->setForI(attackIndex1/75);//
    param->setForJ(attackIndex2);
    param->setForK(attackIndex3);
    param->setForM(attackIndex1%75/15);//
    param->setForN(attackIndex1%75%15/3);//
    param->setForL(attackIndex1%3);//


    for(int i=0; i < param->getTraceNum(); i++){

        

        //读一条
        traceS.readIndexTrace(&trsDataS,i);
        traceR.readIndexTrace(&trsDataR,i); 

        param->setImageDataPoint(trsDataR.data);//param读imagedata参数
        //像素初始化
        for(int j=0;j < param->getGuessSize();j++){ 
            
            
            fmap[*param->getAttackIndex()] = wt[j];
            // param->setFmapPoint(fmap);//param读fmap参数
            
            #if 1

            (*f)(param);
            hw[j][i] = param->getMidHW();
            // printf("%d ", hw[j][i]);

            #endif

        }

        // printf("%d ", i);
        // printf("\n");
        
        for(int j=0; j < param->getPointNum() ; j++){
            sample[j][i]=trsDataS.samples[j+param->getPointNumStart()];
        }  
        
    }

    free(trsDataS.samples);
    free(trsDataS.data);
    free(trsDataS.TSData);

    free(trsDataR.samples);
    free(trsDataR.data);
    free(trsDataR.TSData);


    // outfile->close();
    // free(outfile);
    

    return;

    
    
}



void differentialPowerAnalysis_correlation_distinguish_optimize(Parameters* param, int8_t* (*f)(Parameters*)){

    int bias=50;
    int gap=50;

    TrsData* trsData_result=(TrsData*)malloc(param->getGuessSize() * sizeof(TrsData));
    for(int i=0;i<param->getGuessSize();i++){
        trsData_result[i].samples=(float*)malloc(((param->getTraceNum()-bias)/gap+1) * sizeof(float));
        std::memset(trsData_result[i].samples, 0.0, ((param->getTraceNum()-bias)/gap+1) * sizeof(float));
    }

    // float* result[param->getGuessSize()]={nullptr};
    // for(int i =0 ;i<param->getGuessSize();i++){
    //     result[i]=(float*)malloc(((param->getTraceNum()-bias)/gap+1)*sizeof(float));
    //     memset(result[i], 0.0, ((param->getTraceNum()-bias)/gap+1));
    // }

    float* res_diff = (float*)malloc(param->getPointNum() * sizeof(float));

    //初始化 samples[][]
    float* sample[param->getPointNum()] = {nullptr};
    for(int i=0;i< param->getPointNum() ;i++){
        sample[i]=(float*)malloc(param->getTraceNum()*sizeof(float));
        std::memset(sample[i], 0.0, param->getTraceNum() * sizeof(float));
    }

    //初始化 hw[][]
    uint8_t* hw[param->getGuessSize()] = {nullptr};
    for(int i=0;i<param->getGuessSize();i++){
        hw[i]=(uint8_t*)malloc(param->getTraceNum() * sizeof(uint8_t));
        std::memset(hw[i], 0, param->getTraceNum() * sizeof(uint8_t));
    }

    //计算mid 读入samples
    generate_midvaluehw_samples_dpa(param, f, sample, hw);

    //计算相关性
    for(int index = 0; index < (param->getTraceNum()-bias)/gap+1; index++){

        
        
        for (int i = 0; i < param->getGuessSize(); i++){
            for (int j = 0; j < param->getPointNum(); j++){
                
                //问题出现在这行，检查内存是否溢出？
                res_diff[j] = (float)abs(BaseTools::diff(hw[i], sample[j], bias + index * gap, 25));
                if(i==128){
                    res_diff[j] = 0;
                }
            }
            trsData_result[i].samples[index]=res_diff[BaseTools::findMaxCorr(res_diff,param->getPointNum())];
        }
        #if 0
        printf("%d_max:%f;\n",i-128,result_max[i]);
        #endif


        
    }

    
        
    

    //保存至文件
    ofstream* outfile=new ofstream();   
    outfile->open(param->getOutFile(), ios::out | ios::binary | ios::trunc);
    #if 1//读入 txt
    
    for(int i =0;i<param->getGuessSize();i++){
        for(int j =0; j<(param->getTraceNum()-bias)/gap+1; j++){
            *outfile<<trsData_result[i].samples[j]<<" ";
        }
        *outfile<<"\n";
    }

    #else//读入trs
    ofstream* outfile=new ofstream();   
    outfile->open(param->getOutFile(), ios::out | ios::binary | ios::trunc);

    TrsHead trsHead_result;
    trsHead_result.NT = param->getGuessSize();
    trsHead_result.NS = param->getPointNum();
    trsHead_result.DS = 0;
    trsHead_result.YS = 1;
    trsHead_result.SC = 0x14;//float存储类型
    trsHead_result.GT_length = 0;
    trsHead_result.DC_length = 0;
    trsHead_result.XL_length = 0;
    trsHead_result.YL_length = 0;
    trsHead_result.TS = 0;
    Trace::writeHead(outfile, trsHead_result);
    
    for(int i= 0;i<param->getGuessSize();i++){
        Trace::writeNext(outfile, &trsData_result[i], trsHead_result);
    }
    
    #endif

    //释放内存
    for(int i =0 ;i<param->getGuessSize();i++){
        free(trsData_result[i].samples);
    }
    free(trsData_result);
    outfile->close();
    free(outfile);
    for(int i=0;i < param->getGuessSize(); i++){
        free(hw[i]);
    }
    for(int i=0;i < param->getPointNum();i++){
        free(sample[i]);
    }

}








